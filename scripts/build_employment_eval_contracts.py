"""Build the 3 v1 Employment eval contracts for Phase 5.

This script generates the 3 Employment PDFs that ship the
Phase 5 v1 Employment eval starter, matching the card title
"Phase 5 v1 - Employment eval set (3 contracts EN+DE + 3
expected-deviation YAMLs)". The contract set is:

  examples/contracts/synthetic/employment-001.pdf   (EN stress, ABA-anchored, 3 deviations)
  examples/contracts/synthetic/employment-002.pdf   (EN stress, GOV.UK-anchored, 3 deviations)
  examples/contracts/synthetic-de/employment-001.pdf (DE stress, IHK + BGB-anchored, 3 deviations)

The card (t_5400fec1) is the Phase 5 Employment v1 starter.
The v2 expansion (gated on v1 F1 being acceptable) grows
the set to 10 contracts. The 3 v1 contracts must:

  1. Be text-extractable, deterministic PDFs (reportlab).
  2. Exercise the language="en"/"de" field per clause.
  3. Cover as many of the 5 employment_* baseline values
     + 6 GAP values as 3 contracts of 8 clauses can carry.
  4. Be plausible enough that the spotter's signal is real.

Idempotence: re-running overwrites the 3 PDFs with text-
identical content (pymupdf-extracted text is byte-identical
across runs). The PDF binary itself contains a non-
deterministic /ID hash; the eval harness uses pymupdf's
text extraction which ignores the /ID.
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
SYNTHETIC_EN_DIR = REPO_ROOT / "examples" / "contracts" / "synthetic"
SYNTHETIC_DE_DIR = REPO_ROOT / "examples" / "contracts" / "synthetic-de"


# EN synthetic #1 — ABA-anchored (US-style)
# c1 deviation: 90-day notice (material, over ABA 30-day + US at-will)
# c2 deviation: bonus, no contractual entitlement (material)
# c4 deviation: 30-day notice before cause (minor, courtesy window)
EN_SYNTHETIC_1_TITLE = "EMPLOYMENT AGREEMENT — DRAFT (ABA-ANCHORED)"

EN_SYNTHETIC_1_PARAGRAPHS: list[str] = [
    "This Employment Agreement (the \"Agreement\") is entered into "
    "between the Company and the Employee as of the Effective Date. "
    "The Employee will be employed by the Company on the terms set "
    "forth below. The Company is a Delaware corporation with its "
    "principal place of business in San Francisco, California. The "
    "Employee resides in California. The parties acknowledge that "
    "California law applies to certain obligations under this "
    "Agreement, including non-solicitation enforceability.",

    "1. Notice Period. Either Party may terminate this Agreement "
    "by giving the other Party not less than ninety (90) days' prior "
    "written notice. The notice period shall run from the date of "
    "receipt of the written notice. During the notice period, the "
    "Employee shall continue to perform their duties and the Company "
    "shall continue to compensate the Employee at the Employee's "
    "then-current base salary rate.",

    "2. Compensation. The Company shall pay the Employee an annual "
    "base salary of the amount set out in Schedule A, payable in "
    "equal monthly installments in arrears. Any annual bonus shall "
    "be awarded, if at all, in the sole and absolute discretion of "
    "the Company, and the Employee shall have no contractual "
    "entitlement to any bonus or to any particular level of bonus "
    "in any year. The Employee acknowledges that no representation "
    "has been made as to the amount or likelihood of any bonus.",

    "3. Vacation and Leave. The Employee shall be entitled to "
    "twenty-five (25) paid vacation days per calendar year, "
    "accruing pro rata, in addition to public holidays. Unused "
    "vacation days may be carried over to the following calendar "
    "year, up to a maximum accrual of ten (10) days, beyond which "
    "they will be forfeited. The Employee shall also be entitled "
    "to sick leave, family leave, and other statutory leaves in "
    "accordance with applicable law.",

    "4. Termination for Cause. The Company may terminate this "
    "Agreement for cause, including but not limited to: (a) "
    "material breach of this Agreement by the Employee, (b) "
    "gross misconduct, (c) conviction of a felony, or (d) "
    "sustained unsatisfactory performance. The Company shall "
    "give the Employee not less than thirty (30) days' prior "
    "written notice of any termination under this Section, "
    "specifying the grounds for the termination in reasonable "
    "detail. The Employee shall have the opportunity to cure any "
    "curable breach during the notice period.",

    "5. Non-Solicitation. For a period of twelve (12) months "
    "following the termination of the Employee's employment, "
    "the Employee shall not, directly or indirectly, solicit "
    "any employee, contractor, customer, or client of the "
    "Company with whom the Employee had material contact during "
    "the twelve (12) months preceding termination, for the "
    "purpose of inducing them to terminate or modify their "
    "relationship with the Company.",

    "6. Working Hours. The Employee's normal working hours "
    "shall be 9:00 a.m. to 6:00 p.m. Monday through Friday, "
    "with one (1) hour for lunch. The Employee acknowledges "
    "that the nature of their position may require additional "
    "hours beyond the normal working hours, and the Employee "
    "agrees to work such additional hours as may be reasonably "
    "required.",

    "7. Probationary Period. The first ninety (90) days of the "
    "Employee's employment shall constitute a probationary "
    "period, during which either Party may terminate this "
    "Agreement by giving the other Party not less than seven "
    "(7) days' prior written notice. The Company's exercise "
    "of its termination right during the probationary period "
    "shall not give rise to any claim by the Employee.",

    "8. Confidentiality; Survival. The Employee shall maintain "
    "the confidentiality of all Confidential Information of "
    "the Company both during and after the term of employment, "
    "for a period of three (3) years following termination. "
    "With respect to information that constitutes a trade "
    "secret under applicable law, the confidentiality "
    "obligation shall survive for so long as such information "
    "remains a trade secret.",
]


# EN synthetic #2 — GOV.UK-anchored (UK statutory floor)
# c3 deviation: 15 days leave (material, under WTR 1998 5.6 weeks)
# c5 deviation: 24-month non-solicit (material, TFS Derivatives / Tillman)
# c7 deviation: 10-year confidentiality survival (minor)
EN_SYNTHETIC_2_TITLE = "EMPLOYMENT CONTRACT — DRAFT (GOV.UK-STATUTORY)"

EN_SYNTHETIC_2_PARAGRAPHS: list[str] = [
    "This Employment Contract (the \"Contract\") is entered "
    "into between the Company and the Employee as of the "
    "Effective Date. The Company is a private limited company "
    "registered in England and Wales. The Employee is engaged "
    "as a full-time employee. The employment is subject to the "
    "Employment Rights Act 1996 (ERA) and the Working Time "
    "Regulations 1998 (WTR).",

    "1. Notice Period. Either Party may terminate this Contract "
    "by giving the other Party not less than one (1) week's "
    "written notice during the probationary period, and not less "
    "than one (1) month's written notice thereafter, increasing "
    "by one additional week for each completed year of continuous "
    "service, up to a maximum of twelve (12) weeks' notice after "
    "twelve (12) years of continuous service, in accordance with "
    "section 86 of the Employment Rights Act 1996.",

    "2. Remuneration. The Company shall pay the Employee an "
    "annual gross salary of the amount set out in Schedule A, "
    "payable in equal monthly installments in arrears on or "
    "before the last working day of each month, subject to "
    "deductions for income tax and National Insurance "
    "contributions. The salary shall be reviewed annually in "
    "line with the Company's standard pay review process.",

    "3. Annual Leave. The Employee shall be entitled to fifteen "
    "(15) days' paid annual leave per leave year, in addition "
    "to the eight (8) public holidays in England and Wales. "
    "Leave shall accrue pro rata during the leave year. The "
    "leave year runs from 1 January to 31 December each year.",

    "4. Termination for Cause. The Company may terminate this "
    "Contract summarily for gross misconduct, including but not "
    "limited to: (a) theft or fraud, (b) assault, (c) serious "
    "breach of health and safety rules, (d) gross insubordination, "
    "or (e) being under the influence of alcohol or non-prescribed "
    "drugs at work. Summary dismissal shall be without notice or "
    "pay in lieu of notice. Any other dismissal shall be subject "
    "to the unfair dismissal provisions of section 95 of the "
    "Employment Rights Act 1996.",

    "5. Non-Solicitation. For a period of twenty-four (24) months "
    "following the termination of the Employee's employment, "
    "the Employee shall not, directly or indirectly, solicit or "
    "attempt to solicit any employee, contractor, customer, or "
    "client of the Company with whom the Employee had material "
    "contact during the twelve (12) months preceding termination, "
    "for the purpose of inducing them to terminate or modify their "
    "relationship with the Company.",

    "6. Working Hours. The Employee's normal working hours shall "
    "be 9:00 a.m. to 5:30 p.m. Monday through Friday, with one "
    "(1) hour for lunch. The Employee's normal weekly working "
    "time shall not exceed an average of forty-eight (48) hours "
    "over a seventeen-week reference period, in accordance with "
    "regulation 4 of the Working Time Regulations 1998, unless "
    "the Employee has voluntarily opted out.",

    "7. Confidentiality; Survival. The Employee shall maintain "
    "the confidentiality of all Confidential Information of the "
    "Company both during and after the term of employment, for "
    "a period of ten (10) years following termination. With "
    "respect to information that constitutes a trade secret "
    "under applicable law, the confidentiality obligation shall "
    "survive for so long as such information remains a trade "
    "secret. The Employee shall return all Confidential "
    "Information to the Company upon termination.",

    "8. Probationary Period. The first six (6) months of the "
    "Employee's employment shall constitute a probationary "
    "period, during which the Company may terminate this "
    "Contract by giving the Employee not less than one (1) "
    "week's written notice. During the probationary period, "
    "the Employee is not eligible to bring a claim for unfair "
    "dismissal under section 98 of the Employment Rights Act "
    "1996.",
]


# DE synthetic #1 — IHK + BGB-anchored
# c1 deviation: 6-month notice (material, over BGB § 622)
# c3 deviation: 20 days leave (material, ambiguous vs. BUrlG § 3)
# c4 deviation: 6-week Prüfung (minor, over BGB § 626)
DE_SYNTHETIC_1_TITLE = "ARBEITSVERTRAG — ENTWURF (IHK + BGB-DEFINITION)"

DE_SYNTHETIC_1_PARAGRAPHS: list[str] = [
    "Dieser Arbeitsvertrag (nachfolgend \u201eVertrag\u201c) wird "
    "zwischen dem Arbeitgeber und dem Arbeitnehmer mit Wirkung "
    "zum Eintrittsdatum geschlossen. Der Arbeitgeber ist eine "
    "Gesellschaft mit beschr\u00e4nkter Haftung mit Sitz in M\u00fcnchen, "
    "Bayern. Der Arbeitnehmer wird als Vollzeitkraft eingestellt. "
    "Das Arbeitsverh\u00e4ltnis unterliegt deutschem Recht, insbesondere "
    "dem B\u00fcrgerlichen Gesetzbuch (BGB), dem Bundesurlaubsgesetz "
    "(BUrlG) und dem Arbeitszeitgesetz (ArbZG).",

    "1. K\u00fcndigungsfristen. Das Arbeitsverh\u00e4ltnis kann von beiden "
    "Parteien unter Einhaltung einer K\u00fcndigungsfrist von sechs "
    "(6) Monaten zum Monatsende ordentlich gek\u00fcndigt werden. Die "
    "K\u00fcndigung bedarf der Schriftform. W\u00e4hrend der K\u00fcndigungsfrist "
    "ist der Arbeitnehmer unter Fortzahlung der Verg\u00fctung von der "
    "Arbeitspflicht freizustellen. Eine K\u00fcrzung des Urlaubsanspruchs "
    "f\u00fcr die Zeit der Freistellung ist ausgeschlossen.",

    "2. Verg\u00fctung. Der Arbeitnehmer erh\u00e4lt eine monatliche "
    "Bruttoverg\u00fctung in der in Anlage A vereinbarten H\u00f6he, die am "
    "Monatsende auf das vom Arbeitnehmer benannte Bankkonto "
    "\u00fcberwiesen wird. Die Verg\u00fctung wird j\u00e4hrlich zum 1. Januar "
    "\u00fcberpr\u00fcft und an die tarifliche Entwicklung angepasst. "
    "Zus\u00e4tzlich erh\u00e4lt der Arbeitnehmer ein 13. Monatsgehalt, "
    "das jeweils zur H\u00e4lfte im Juni und im November ausgezahlt "
    "wird.",

    "3. Urlaub. Der Arbeitnehmer hat Anspruch auf einen "
    "Jahresurlaub von zwanzig (20) Arbeitstagen bei einer "
    "F\u00fcnf-Tage-Woche, zuz\u00fcglich der gesetzlichen Feiertage am "
    "Betriebsort. Der Urlaub ist in Abstimmung mit dem Arbeitgeber "
    "zu nehmen und ist nach M\u00f6glichkeit in zusammenh\u00e4ngenden "
    "Abschnitten zu gew\u00e4hren. Eine \u00dcbertragung auf das n\u00e4chste "
    "Kalenderjahr ist nur in begr\u00fcndeten Ausnahmef\u00e4llen m\u00f6glich.",

    "4. Au\u00dferordentliche K\u00fcndigung. Das Recht zur au\u00dferordentlichen "
    "K\u00fcndigung gem\u00e4\u00df \u00a7 626 BGB bleibt unber\u00fchrt. Ein wichtiger "
    "Grund liegt insbesondere vor bei schweren Pflichtverletzungen, "
    "Arbeitsverweigerung, strafbaren Handlungen oder nachhaltiger "
    "Verletzung der arbeitsvertraglichen Pflichten. Vor Ausspruch "
    "einer au\u00dferordentlichen K\u00fcndigung hat der Arbeitgeber eine "
    "Frist von sechs (6) Wochen zur Pr\u00fcfung des Sachverhalts "
    "einzuhalten.",

    "5. Wettbewerbsverbot und Nebent\u00e4tigkeit. Dem Arbeitnehmer ist "
    "es f\u00fcr die Dauer von zw\u00f6lf (12) Monaten nach Beendigung des "
    "Arbeitsverh\u00e4ltnisses untersagt, in Konkurrenz zum Arbeitgeber "
    "t\u00e4tig zu werden, Kunden abzuwerben oder Mitarbeiter abzuwerben. "
    "Eine Karenzentsch\u00e4digung wird nicht gezahlt, da das Verbot "
    "der Dauer des Arbeitsverh\u00e4ltnisses entspricht und der "
    "Arbeitnehmer w\u00e4hrend des Arbeitsverh\u00e4ltnisses ausreichend "
    "vergoltet wurde.",

    "6. Arbeitszeit. Die regelm\u00e4\u00dfige w\u00f6chentliche Arbeitszeit "
    "betr\u00e4gt vierzig (40) Stunden, verteilt auf f\u00fcnf (5) Werktage "
    "von Montag bis Freitag. Die t\u00e4gliche Arbeitszeit darf acht "
    "(8) Stunden nicht \u00fcberschreiten; sie kann auf bis zu zehn "
    "(10) Stunden verl\u00e4ngert werden, wenn im Durchschnitt von "
    "sechs (6) Kalendermonaten acht (8) Stunden nicht \u00fcberschritten "
    "werden, gem\u00e4\u00df \u00a7 3 ArbZG.",

    "7. Probezeit. Die ersten sechs (6) Monate des Arbeitsverh\u00e4ltnisses "
    "gelten als Probezeit. W\u00e4hrend der Probezeit kann das "
    "Arbeitsverh\u00e4ltnis von beiden Parteien mit einer Frist von zwei "
    "(2) Wochen gek\u00fcndigt werden, gem\u00e4\u00df \u00a7 622 Abs. 3 BGB. Die "
    "K\u00fcndigung bedarf der Schriftform. Eine K\u00fcndigungsschutzklage "
    "ist w\u00e4hrend der Probezeit nicht m\u00f6glich.",

    "8. Verschwiegenheit; Fortbestand. Der Arbeitnehmer verpflichtet "
    "sich, alle Betriebs- und Gesch\u00e4ftsgeheimnisse des Arbeitgebers "
    "w\u00e4hrend und nach Beendigung des Arbeitsverh\u00e4ltnisses geheim "
    "zu halten. Die Verpflichtung besteht f\u00fcr einen Zeitraum von "
    "drei (3) Jahren nach Beendigung des Arbeitsverh\u00e4ltnisses "
    "fort. F\u00fcr Gesch\u00e4ftsgeheimnisse im Sinne des \u00a7 2 Nr. 1 GeschGehG "
    "besteht die Verpflichtung so lange, wie die jeweilige Information "
    "die Voraussetzungen des \u00a7 2 Nr. 1 GeschGehG erf\u00fcllt.",
]


def build_pdf(out_path: Path, title: str, paragraphs: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 10
    body_style.leading = 13

    story: list = [Paragraph(f"<b>{title}</b>", styles["Heading1"])]
    story.append(Spacer(1, 12))
    for para in paragraphs:
        story.append(Paragraph(para, body_style))
        story.append(Spacer(1, 6))

    doc.build(story)


def main() -> int:
    SYNTHETIC_EN_DIR.mkdir(parents=True, exist_ok=True)
    SYNTHETIC_DE_DIR.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[Path, str, list[str]]] = [
        (
            SYNTHETIC_EN_DIR / "employment-001.pdf",
            EN_SYNTHETIC_1_TITLE,
            EN_SYNTHETIC_1_PARAGRAPHS,
        ),
        (
            SYNTHETIC_EN_DIR / "employment-002.pdf",
            EN_SYNTHETIC_2_TITLE,
            EN_SYNTHETIC_2_PARAGRAPHS,
        ),
        (
            SYNTHETIC_DE_DIR / "employment-001.pdf",
            DE_SYNTHETIC_1_TITLE,
            DE_SYNTHETIC_1_PARAGRAPHS,
        ),
    ]

    for path, title, paragraphs in targets:
        build_pdf(path, title, paragraphs)
        print(f"wrote {path} ({path.stat().st_size} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
